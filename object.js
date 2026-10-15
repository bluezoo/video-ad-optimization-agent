/*
Statuses used for *both* overall status of campaigns *and* status of individual videos; these are often accompanied by status_meta info describing additional details such as how many items are affected, when something is expected to be done or has been done, etc.
*/
const Status = {
  NONE: 0,
  GENERATING_ACTIVE: 1,
  GENERATING_COMPLETE: 2,
  GENERATING_FAILED: 3, // Needed?
  REVIEW_NEEDED: 4,
  APPROVAL_UPDATED: 5,
  TESTING_ACTIVE: 6,
  TESTING_COMPLETE: 7,
  TESTING_FAILED: 8, // Needed?
}


/*
Campaign, with empty 'videos' collection (video objects described further below); this object would also be used for templates
*/
let campaignExample = {
  "id": "000001", // Some sort of unique id
  "name": "Spring/Summer Sport Sunglasses",
  "owner": "cid@domain.com", // Account id/name
  // Simple access control info; no need to support anything real
  "shared_with": [ "tommy@domain.com", "fred@domain.com", ],
  "created_date": "2026-01-01T00:00:00Z", // Date created
  "modified_date": "2026-01-01T00:00:00Z", // Date modified
  "is_template": false, // Whether this is a template
  "is_favorite": false, // Whether this is marked as a favorite
  "is_archived": false, // Whether this is archived
  "status": Status.TESTING_ACTIVE, // Overall status
  "status_meta": { // Add'l status info; not all fields are always applicable
    "quantity": 10,
    "end_date": "2026-01-01T00:00:00Z",
    // "message": "Failed to connect to testing server",
  },
  "thumbnail": "/generated_assets/000001.jpg",
  "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
  // *Default* settings, to be used for generating videos variants; specific
  // overrides to these settings are stored on individual videos
  "settings": {  
    "overall": { // Prompt + files indicating what occurs in the video
      "prompt": "Lorem ipsum dolor sit amet",
      "files": [
        "http://example.com/script.txt",
      ],
    },
    "items": { // Prompt + files describing items shown in the video
      "prompt": "Lorem ipsum dolor sit amet",
      "files": [
        "http://example.com/script.txt",
      ],
    },
    "people": { // Prompt + files describing people in the video
      "prompt": "Lorem ipsum dolor sit amet",
      "files": [
        "http://example.com/script.txt",
      ],
    },
    "performance": { // Prompt + files describing actions in the video
      "prompt": "Lorem ipsum dolor sit amet",
      "files": [
        "http://example.com/script.txt",
      ],
    },
    "setting": { // Prompt + files describing setting in the video
      "prompt": "Lorem ipsum dolor sit amet",
      "files": [
        "http://example.com/script.txt",
      ],
    },
    "audio": { // Prompt + files describing speech & music in the video
      "prompt": "Lorem ipsum dolor sit amet",
      "files": [
        "http://example.com/script.txt",
      ],
    },
    "languages": [ "en-US", ], // Languages used in generated videos
    "guidelines": [ // Brand & content guidelines
      "http://example.com/script.txt",
    ],
    "format": {
      "duration": 8, // Duration of generated videos, in seconds
      "aspect_ratios": [ "16:9", ], // Aspect ratios of generated videos
      "resolution": "1080p", // Resolution of generated videos
    },
    "testing": { // For generating + testing videos
      "variants_per_generation": 10, // Number of variants to generate per batch
      "rules": "http://example.com/rules.json", // Needed?
      "duration": 24, // How long to test for, in hours
    },
  },
  // Access/edit activity log; might not need this...
  /*
  "activity": [
    {
      "date": "2026-01-01T00:00:00Z",
      "action": "edited",
      "performed_by": "cid@domain.com",
    },
  ],
  */
  "videos": [
    // ...
  ], // Collection of videos; example video further below
}


// Video approval statuses
const ApprovalStatus = {
  NONE: 0,
  APPROVED: 1,
  REJECTED: 2,
}


/*
Video; I'm not sure how much additional info would be needed to assist with
testing via the CMS, etc.
*/
let videoExample = {
  "id": "000001", // Some sort of unique id
  "name": "000-000-001",
  "parent_id": "000000", // Unique id of parent video, as applicable
  // "campaign_id": "000001", // Unique id of parent campaign; needed?
  "created_date": "2026-01-01T00:00:00Z", // Date created
  // "modified_date": "2026-01-01T00:00:00Z", // Date modified; not needed?
  "is_favorite": false, // Whether the video is marked as a favorite
  "is_archived": false, // Whether the video is archived
  "approval_status": ApprovalStatus.APPROVED, // Approval status
  "approval_date": "2026-01-01T00:00:00Z", // Date approved
  "status": Status.TESTING_ACTIVE, // Overall status
  "status_meta": { // Add'l status info; not all fields are always applicable
    "quantity": 10,
    "end_date": "2026-01-01T00:00:00Z",
    // "message": "Failed to connect to testing server",
  },
  "thumbnail": "/generated_assets/000001_000001.jpg",
  "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
  "url": "/generated_assets/000001_000001.mp4",
  "testing_period": {
    "start_date": "2026-01-01T00:00:00Z",
    "end_date": "2026-01-01T00:00:00Z",
  },
  "duration": 8, // Duration, in seconds
  "impressions": 1000, // Number of impressions
  "impressions_id": "abcd1243", // Unique id using to display impressions data
  "revenue": 123.45, // Revenue generated
  "revenue_id": "efgh5678", // Unique id using to display revenue data
  "rank": 5, // Overall rank, given outcome from testing
  // Access/edit activity log; might not need this...
  /*
  "activity": [
    {
      "date": "2026-01-01T00:00:00Z",
      "action": "edited",
      "performed_by": "cid@domain.com",
    },
  ],
  */
  // Settings *overrides*, to be applied to / inherited by subsequent variants;
  // only those fields that differ from the parent campaign settings are stored
  "settings": {  
    // "overall": {
    //   "prompt": "Lorem ipsum dolor sit amet",
    //   "files": [
    //     "http://example.com/script.txt",
    //   ],
    // },
    // ...
  },
  // "timeline_feedback": null, // Not sure what to do here yet
}